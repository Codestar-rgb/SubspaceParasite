package com.srp.client.renderer;

import com.srp.client.model.InfVillagerHeadModel;
import com.srp.entity.InfVillagerHeadEntity;
import software.bernie.geckolib.renderer.GeoEntityRenderer;
import net.minecraft.client.renderer.entity.EntityRendererProvider;

public class InfVillagerHeadRenderer extends GeoEntityRenderer<InfVillagerHeadEntity> {

    public InfVillagerHeadRenderer(EntityRendererProvider.Context renderManager) {
        super(renderManager, new InfVillagerHeadModel());
    }
}
