package com.srp.client.renderer;

import com.srp.client.model.HiGolemModel;
import com.srp.entity.HiGolemEntity;
import software.bernie.geckolib.renderer.GeoEntityRenderer;
import net.minecraft.client.renderer.entity.EntityRendererProvider;

public class HiGolemRenderer extends GeoEntityRenderer<HiGolemEntity> {

    public HiGolemRenderer(EntityRendererProvider.Context renderManager) {
        super(renderManager, new HiGolemModel());
    }
}
