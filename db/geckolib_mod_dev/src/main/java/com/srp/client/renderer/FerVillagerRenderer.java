package com.srp.client.renderer;

import com.srp.client.model.FerVillagerModel;
import com.srp.entity.FerVillagerEntity;
import software.bernie.geckolib.renderer.GeoEntityRenderer;
import net.minecraft.client.renderer.entity.EntityRendererProvider;

public class FerVillagerRenderer extends GeoEntityRenderer<FerVillagerEntity> {

    public FerVillagerRenderer(EntityRendererProvider.Context renderManager) {
        super(renderManager, new FerVillagerModel());
    }
}
